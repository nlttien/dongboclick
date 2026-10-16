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

import collections
import json
import os
import signal
import sys
import time
import threading

try:
    import websocket          # websocket-client
except ImportError:
    print("[!] Thiếu thư viện. Cài đặt trước:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

# ------------------------------------------------------------------
#  CẤU HÌNH
# ------------------------------------------------------------------
def _config_dir():
    """Thư mục chứa config.json: cạnh file .AppImage / .exe / agent.py (người dùng sửa được).
    Không ghi được ở đó (vd AppImage trong thư mục chỉ đọc) -> ~/.config/clickdongbo."""
    if os.environ.get("APPIMAGE"):
        # Bên trong AppImage là ổ chỉ đọc -> dùng thư mục chứa chính file .AppImage
        d = os.path.dirname(os.path.abspath(os.environ["APPIMAGE"]))
    elif getattr(sys, "frozen", False):
        d = os.path.dirname(sys.executable)
    else:
        d = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(d, "config.json")) or os.access(d, os.W_OK):
        return d
    d = os.path.join(os.path.expanduser("~"), ".config", "clickdongbo")
    os.makedirs(d, exist_ok=True)
    return d


BASE_DIR = _config_dir()
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "server": "ws://192.168.2.113:7000/ws",
    "channel": "room1",
    "name": "May-A",
    "backend": "auto",         # auto | evdev (Linux, X11 + Wayland) | pynput
    "relay_keys": True,        # có nghe & gửi phím đi không
    "auto_inject": True,       # máy nhận có tự bấm phím không
    "echo_suppress_ms": 90,    # khoảng thời gian chống lặp vòng (ms)
    "only_keys": [],           # nếu khác rỗng: CHỈ relay các phím này
    "ignore_keys": [],         # các phím bỏ qua
    "pause_key": "insert",     # phím TẮT đồng bộ = tạm dừng (không gửi, không nhận); "" = không dùng
    "resume_key": "delete",    # phím BẬT lại đồng bộ; trùng pause_key = 1 phím bật/tắt luân phiên
    "start_paused": False,     # khởi động ở trạng thái tạm dừng
    "ui_port": 7071,           # giao diện web http://127.0.0.1:<ui_port>/ ; 0 = tắt
    "open_ui": True            # tự mở giao diện trong trình duyệt khi chạy
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

# Cho phép ghi đè bằng tham số dòng lệnh: python agent.py [name] [channel] [server] [--no-ui] [--no-browser]
FLAGS = {a for a in sys.argv[1:] if a.startswith("--")}
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(ARGS) >= 1:
    cfg["name"] = ARGS[0]
if len(ARGS) >= 2:
    cfg["channel"] = ARGS[1]
if len(ARGS) >= 3:
    cfg["server"] = ARGS[2]

# ------------------------------------------------------------------
#  CHỌN BACKEND BÀN PHÍM
# ------------------------------------------------------------------
# Linux: evdev (linux_input.py) — chạy cả X11 lẫn Wayland, không có echo.
# Windows/macOS (hoặc Linux X11 nếu đặt "backend": "pynput"): pynput.
BACKEND = str(cfg.get("backend") or "auto").lower()
if BACKEND == "auto":
    BACKEND = "evdev" if sys.platform.startswith("linux") else "pynput"

if BACKEND == "evdev":
    try:
        import linux_input
    except ImportError as e:
        print("[!] Thiếu thư viện evdev (%s). Cài:  pip install -r requirements.txt" % e)
        sys.exit(1)
else:
    try:
        from pynput import keyboard
        from pynput.keyboard import Key, Controller
    except ImportError as e:
        print("[!] Không nạp được pynput (%s)." % e)
        print("    pip install -r requirements.txt")
        sys.exit(1)

# ------------------------------------------------------------------
#  TRẠNG THÁI
# ------------------------------------------------------------------
kbd = None               # pynput Controller hoặc linux_input.Injector (tạo trong main)
ws_app = None
lock = threading.Lock()
last_inject_time = 0.0   # thời điểm gần nhất agent tự bấm phím (chống echo)
connected = False        # đang kết nối tới server hay không
stop = threading.Event() # đặt khi Ctrl+C -> thoát hẳn, không kết nối lại
paused = threading.Event()  # đang TẠM DỪNG: không gửi phím đi, không tự bấm phím nhận về
listener = None

# Trạng thái cho giao diện web
events = collections.deque(maxlen=200)  # nhật ký gần nhất
event_seq = 0
roster = []              # tên các máy online trong kênh
warnings = []            # thiếu quyền / lỗi cấu hình
stats = {"sent": 0, "received": 0, "last_sent": None, "last_recv": None}


def log(kind, text):
    """In ra console + lưu cho giao diện web. kind: info | warn | send | recv | state."""
    global event_seq
    try:
        print(text)
    except Exception:
        pass  # console không ghi được (vd chạy không có terminal)
    with lock:
        event_seq += 1
        events.append({"seq": event_seq, "t": time.time(), "kind": kind,
                       "text": text.replace("\a", "").strip()})


def pause_key():
    return str(cfg.get("pause_key") or "").strip().lower()


def resume_key():
    return str(cfg.get("resume_key") or "").strip().lower()

# Các phím bổ trợ — KHÔNG relay riêng để tránh nhân đôi shift/ctrl khi gõ chữ
MODIFIERS = {
    "shift", "shift_l", "shift_r",
    "ctrl", "ctrl_l", "ctrl_r",
    "alt", "alt_l", "alt_r", "alt_gr",
    "cmd", "cmd_l", "cmd_r",
    "fn", "caps_lock", "num_lock", "scroll_lock"
}

# Ánh xạ tên phím đặc biệt -> đối tượng Key của pynput
SPECIAL = {}
if BACKEND == "pynput":
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
    if BACKEND == "evdev":
        return False  # evdev không nghe bàn phím ảo của chính agent -> không có echo
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
    if kbd is None:
        return
    if BACKEND == "evdev":
        try:
            if not kbd.tap(obj):
                log("warn", "[inject] bỏ qua phím không hỗ trợ: %s" % key_label(obj))
        except OSError as e:
            log("warn", "[inject err] %s" % e)
        return
    key_obj = deserialize(obj)
    if key_obj is None:
        return
    mark_inject()  # ĐÁNH DẤU để bỏ qua tiếng vang của chính mình
    try:
        kbd.press(key_obj)
        kbd.release(key_obj)
    except Exception as e:
        log("warn", "[inject err] %s" % e)


# ------------------------------------------------------------------
#  LẮNG NGHE PHÍM TOÀN CỤC
# ------------------------------------------------------------------
def on_press(key):
    """Callback của pynput."""
    handle_local(serialize(key))


def control_key(obj):
    """'pause' | 'resume' | 'toggle' nếu obj là phím điều khiển tạm dừng, ngược lại None."""
    if obj is None:
        return None
    name = str(key_label(obj)).lower()
    pk, rk = pause_key(), resume_key()
    if pk and name == pk:
        return "toggle" if pk == rk else "pause"
    if rk and name == rk:
        return "resume"
    return None


def print_pause_state():
    if paused.is_set():
        how = resume_key() or pause_key()
        log("state", "\a[⏸] TẠM DỪNG — không gửi, không nhận phím." +
            (" Bấm [%s] để bật lại." % how if how else ""))
    else:
        log("state", "\a[▶] ĐÃ BẬT đồng bộ phím.")


def set_paused(want):
    """Đổi trạng thái tạm dừng; chỉ in/bíp khi trạng thái thực sự đổi."""
    if want == paused.is_set():
        return
    if want:
        paused.set()
    else:
        paused.clear()
    print_pause_state()


def handle_local(obj):
    """Một phím vừa được nhấn trên máy này (từ pynput hoặc evdev)."""
    if is_echo():
        return  # sự kiện do chính máy vừa bấm (để tránh lặp vòng)
    action = control_key(obj)
    if action:
        # phím điều khiển chỉ có tác dụng trên máy này, không gửi đi
        set_paused(not paused.is_set() if action == "toggle" else action == "pause")
        return
    if paused.is_set() or not cfg.get("relay_keys", True):
        return
    if not should_relay(obj):
        return
    send_event(obj)
    # Chỉ ghi khi đã kết nối (tránh spam khi mất mạng)
    if connected:
        stats["sent"] += 1
        stats["last_sent"] = key_label(obj)
        log("send", "  [gửi] phím: %s" % key_label(obj))


def start_listener():
    global listener
    if BACKEND == "evdev":
        listener = linux_input.Listener(handle_local)
        listener.start()
        return listener
    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    return listener


def ensure_injector():
    """Tạo bộ bấm phím nếu chưa có (lúc khởi động, hoặc khi bật "tự bấm" từ giao diện)."""
    global kbd
    if kbd is not None:
        return True
    if BACKEND == "evdev":
        try:
            kbd = linux_input.Injector()
        except OSError as e:
            log("warn", "[!] Không tạo được bàn phím ảo (%s) -> không tự bấm phím được." % e)
            return False
    else:
        kbd = Controller()
    return True


# ------------------------------------------------------------------
#  WEBSOCKET
# ------------------------------------------------------------------
def on_open(ws):
    global connected
    connected = True
    log("info", "[+] Đã kết nối server: %s" % cfg["server"])
    try:
        ws.send(json.dumps({
            "type": "join",
            "name": cfg["name"],
            "channel": cfg["channel"]
        }))
    except Exception as e:
        log("warn", "[join err] %s" % e)
    print("[i] Đang nghe phím toàn cục. Bấm phím bất kỳ để đồng bộ.")
    pk, rk = pause_key(), resume_key()
    if pk == rk and pk:
        print("[i] Bấm [%s] để TẮT / BẬT đồng bộ." % pk)
    else:
        if pk:
            print("[i] Bấm [%s] để TẮT đồng bộ (tạm dừng)." % pk)
        if rk:
            print("[i] Bấm [%s] để BẬT lại đồng bộ." % rk)
    if paused.is_set():
        print_pause_state()
    print("[i] Ctrl+C để thoát.")


def on_message(ws, message):
    try:
        msg = json.loads(message)
    except Exception:
        return

    if msg.get("type") == "roster":
        roster[:] = [str(n) for n in (msg.get("clients") or [])]
        return
    if msg.get("type") != "sync":
        return
    if msg.get("key") != "keystroke":
        return
    try:
        data = json.loads(msg.get("value") or "{}")
    except Exception:
        return

    obj = data.get("s")
    if control_key(obj) or not should_relay(obj):
        return

    src = msg.get("from", "?")
    if paused.is_set():
        return  # tạm dừng: bỏ qua hoàn toàn (không bấm, không đếm)
    stats["received"] += 1
    stats["last_recv"] = {"key": key_label(obj), "from": src}
    active = cfg.get("auto_inject", True) and kbd is not None
    log("recv", "  [nhận] %s bấm phím: %s%s" % (src, key_label(obj), "" if active else "  (không bấm — đang tắt tự bấm)"))
    if active:
        inject_key(obj)


def on_error(ws, error):
    # Im lặng: on_close đã thông báo. Tránh spam "WinError 10061" lặp lại.
    pass


def on_close(ws, *args):
    global connected
    was = connected
    connected = False
    roster[:] = []
    if stop.is_set() or reconnecting.is_set():
        return  # đang thoát do Ctrl+C, hoặc chủ động kết nối lại sau khi đổi cấu hình
    if was:
        log("warn", "[-] Mất kết nối server (%s). Đang thử lại..." % cfg["server"])
    print("[-] Chưa kết nối được server (" + cfg["server"] + ").")
    print("    -> Hãy chắc chắn server đang chạy:  npm start")
    print("    -> Và 'server' trong config.json trỏ đúng IP/cổng. Đang thử lại...")


# ------------------------------------------------------------------
#  GIAO DIỆN WEB (ui_server.py)
# ------------------------------------------------------------------
reconnecting = threading.Event()  # đặt khi đổi cấu hình -> vòng lặp kết nối lại ngay
EDITABLE = ("server", "channel", "name", "pause_key", "resume_key")


def get_state():
    if BACKEND == "evdev" and listener is not None:
        kbds = sorted({d.name for d in list(listener.devices.values())})
    elif listener is not None:
        kbds = ["Toàn bộ bàn phím (pynput)"]
    else:
        kbds = []
    with lock:
        log_copy = list(events)
    return {
        "name": cfg["name"], "channel": cfg["channel"], "server": cfg["server"],
        "pause_key": pause_key(), "resume_key": resume_key(),
        "backend": BACKEND, "connected": connected, "paused": paused.is_set(),
        "relay_keys": bool(cfg.get("relay_keys", True)),
        "auto_inject": bool(cfg.get("auto_inject", True)) and kbd is not None,
        "roster": list(roster), "keyboards": kbds, "warnings": list(warnings),
        "sent": stats["sent"], "received": stats["received"],
        "last_sent": stats["last_sent"], "last_recv": stats["last_recv"],
        "log": log_copy, "config_path": CONFIG_PATH,
    }


def reconnect():
    reconnecting.set()
    if ws_app is not None:
        ws_app.close()


def do_action(action, data):
    if action == "set_paused":
        set_paused(bool(data.get("paused")))
    elif action == "set_option":
        key = data.get("key")
        if key not in ("relay_keys", "auto_inject"):
            raise ValueError("tùy chọn không hợp lệ")
        value = bool(data.get("value"))
        if key == "auto_inject" and value and not ensure_injector():
            raise ValueError("không tạo được bàn phím ảo (xem cảnh báo quyền)")
        cfg[key] = value
        save_config(cfg)
        log("info", "[i] %s = %s" % (key, value))
    elif action == "quit":
        log("info", "[i] Thoát theo yêu cầu từ giao diện.")
        stop.set()
        if ws_app is not None:
            ws_app.close()
    elif action == "save_config":
        new = data.get("config") or {}
        server = str(new.get("server", cfg["server"])).strip()
        if not server.startswith(("ws://", "wss://")):
            raise ValueError("server phải bắt đầu bằng ws:// hoặc wss://")
        for k in EDITABLE:
            if k in new:
                cfg[k] = str(new[k]).strip()
        cfg["server"] = server
        save_config(cfg)
        log("info", "[i] Đã lưu cấu hình (%s), kết nối lại..." % CONFIG_PATH)
        reconnect()
    else:
        raise ValueError("action không hợp lệ")
    return None


def already_running(port):
    """Nếu agent khác đang chạy (cổng giao diện đã có agent) -> trả về URL của nó."""
    import urllib.request
    url = "http://127.0.0.1:%d/" % port
    try:
        with urllib.request.urlopen(url + "api/state", timeout=1) as r:
            if "backend" in json.loads(r.read().decode("utf-8")):
                return url
    except Exception:
        pass
    return None


def main():
    # Mở AppImage/exe lần 2 (vd double-click) -> chỉ mở lại giao diện của bản đang chạy
    port = int(cfg.get("ui_port") or 0)
    if port and "--no-ui" not in FLAGS:
        url = already_running(port)
        if url:
            print("[i] Agent đã chạy sẵn -> mở giao diện: " + url)
            if "--no-browser" not in FLAGS:
                import webbrowser
                webbrowser.open(url)
            return

    print("=" * 60)
    print("  CLICK-DONGBO — Keystroke Sync Agent")
    print("=" * 60)
    print("  Tên máy : %s" % cfg["name"])
    print("  Kênh     : %s" % cfg["channel"])
    print("  Server   : %s" % cfg["server"])
    print("  Backend  : %s" % BACKEND)
    print("-" * 60)

    # Vẫn phải nghe phím nếu có phím tạm dừng, kể cả khi relay_keys = false
    want_listen = cfg.get("relay_keys", True) or bool(pause_key() or resume_key())
    if cfg.get("start_paused"):
        paused.set()
    want_inject = cfg.get("auto_inject", True)
    if BACKEND == "evdev":
        # Thiếu quyền -> vẫn chạy phần còn dùng được, kèm hướng dẫn sửa
        warnings.extend(linux_input.check_permissions(want_listen, want_inject))
    if want_inject:
        ensure_injector()
    if want_listen:
        start_listener()

    # Giao diện web cục bộ
    if port and "--no-ui" not in FLAGS:
        import ui_server
        url = ui_server.start(port, get_state, do_action)
        if url:
            log("info", "[i] Giao diện: %s" % url)
            if cfg.get("open_ui", True) and "--no-browser" not in FLAGS:
                import webbrowser
                threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()

    # websocket-client tự nuốt KeyboardInterrupt trong run_forever() rồi return bình thường
    # -> vòng lặp dưới sẽ kết nối lại mãi, Ctrl+C không thoát được. Tự bắt SIGINT để dừng hẳn.
    def on_sigint(signum, frame):
        stop.set()
        if ws_app is not None:
            ws_app.close()

    signal.signal(signal.SIGINT, on_sigint)

    # Vòng lặp kết nối lại nếu rớt
    while not stop.is_set():
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
        if reconnecting.is_set():
            reconnecting.clear()  # đổi cấu hình -> kết nối lại ngay với cfg mới
            continue
        stop.wait(2)  # chờ rồi kết nối lại (Ctrl+C cắt ngang được)
    print("\n[!] Thoát.")
    if kbd is not None and BACKEND == "evdev":
        kbd.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Thoát.")
