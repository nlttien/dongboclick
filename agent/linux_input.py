# -*- coding: utf-8 -*-
"""
Backend bàn phím cho Linux dùng evdev trực tiếp (chạy được cả X11 lẫn Wayland).

Vì sao không dùng pynput trên Linux:
  - backend 'xorg' của pynput không bắt được phím toàn cục trên Wayland;
  - backend 'uinput' của pynput gọi `dumpkeys` (cần root) và chỉ nghe 1 thiết bị —
    thường lại chọn nhầm bàn phím ảo do chính Controller tạo ra.

Ở đây:
  - Nghe   : đọc MỌI bàn phím thật trong /dev/input/event* (cần nhóm `input`),
             tự nhận bàn phím cắm thêm, BỎ QUA bàn phím ảo của agent -> không có echo.
  - Bấm    : tạo 1 bàn phím ảo qua /dev/uinput (cần quyền ghi, xem setup-linux.sh).
  - Ký tự  : quy đổi keycode <-> ký tự theo layout US (không cần dumpkeys/root).

Định dạng phím trao đổi giống agent.py: {"k": "char", "v": "a"} hoặc {"k": "special", "v": "enter"}
(tên special trùng tên Key của pynput để máy Windows và Linux hiểu nhau).
"""

import os
import select
import threading
import time

import evdev
from evdev import ecodes as e

VIRTUAL_NAME = "clickdongbo-agent"

# ---- Bảng ký tự layout US: keycode -> (thường, có Shift) -------------------
CHARS = {}
for _c in "abcdefghijklmnopqrstuvwxyz":
    CHARS[getattr(e, "KEY_" + _c.upper())] = (_c, _c.upper())
for _d, _s in zip("1234567890", "!@#$%^&*()"):
    CHARS[getattr(e, "KEY_" + _d)] = (_d, _s)
CHARS.update({
    e.KEY_MINUS: ("-", "_"), e.KEY_EQUAL: ("=", "+"),
    e.KEY_LEFTBRACE: ("[", "{"), e.KEY_RIGHTBRACE: ("]", "}"),
    e.KEY_BACKSLASH: ("\\", "|"), e.KEY_SEMICOLON: (";", ":"),
    e.KEY_APOSTROPHE: ("'", '"'), e.KEY_GRAVE: ("`", "~"),
    e.KEY_COMMA: (",", "<"), e.KEY_DOT: (".", ">"), e.KEY_SLASH: ("/", "?"),
})
# Bàn phím số: chỉ nghe (khi bấm lại sẽ dùng phím số hàng trên)
KEYPAD = {getattr(e, "KEY_KP" + _d): _d for _d in "0123456789"}
KEYPAD.update({e.KEY_KPPLUS: "+", e.KEY_KPMINUS: "-", e.KEY_KPASTERISK: "*",
               e.KEY_KPSLASH: "/", e.KEY_KPDOT: "."})

# ký tự -> (keycode, cần Shift?)
CHAR_TO_KEY = {}
for _code, (_n, _s) in CHARS.items():
    CHAR_TO_KEY[_n] = (_code, False)
    CHAR_TO_KEY[_s] = (_code, True)
CHAR_TO_KEY[" "] = (e.KEY_SPACE, False)

# ---- Phím đặc biệt: tên (theo pynput Key) <-> keycode ---------------------
SPECIAL = {
    "space": e.KEY_SPACE, "enter": e.KEY_ENTER, "tab": e.KEY_TAB,
    "backspace": e.KEY_BACKSPACE, "esc": e.KEY_ESC,
    "delete": e.KEY_DELETE, "insert": e.KEY_INSERT,
    "home": e.KEY_HOME, "end": e.KEY_END,
    "page_up": e.KEY_PAGEUP, "page_down": e.KEY_PAGEDOWN,
    "up": e.KEY_UP, "down": e.KEY_DOWN, "left": e.KEY_LEFT, "right": e.KEY_RIGHT,
    "caps_lock": e.KEY_CAPSLOCK, "num_lock": e.KEY_NUMLOCK, "scroll_lock": e.KEY_SCROLLLOCK,
    "print_screen": e.KEY_SYSRQ, "pause": e.KEY_PAUSE, "menu": e.KEY_COMPOSE,
    "shift": e.KEY_LEFTSHIFT, "shift_r": e.KEY_RIGHTSHIFT,
    "ctrl": e.KEY_LEFTCTRL, "ctrl_r": e.KEY_RIGHTCTRL,
    "alt": e.KEY_LEFTALT, "alt_gr": e.KEY_RIGHTALT,
    "cmd": e.KEY_LEFTMETA, "cmd_r": e.KEY_RIGHTMETA,
}
for _i in range(1, 25):
    SPECIAL["f%d" % _i] = getattr(e, "KEY_F%d" % _i)
# Bí danh khi nhận (pynput có thể gửi các tên này)
SPECIAL_ALIASES = {"return": "enter", "escape": "esc", "shift_l": "shift",
                   "ctrl_l": "ctrl", "alt_l": "alt", "alt_r": "alt_gr", "cmd_l": "cmd"}
CODE_TO_SPECIAL = {code: name for name, code in SPECIAL.items()}
CODE_TO_SPECIAL[e.KEY_KPENTER] = "enter"

SHIFT_CODES = {e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT}


def translate(code, shift=False, caps=False):
    """keycode (+ trạng thái Shift/CapsLock) -> dict phím, hoặc None nếu không hỗ trợ."""
    if code in CHARS:
        normal, shifted = CHARS[code]
        upper = shift != (caps and normal.isalpha())  # CapsLock chỉ đổi chữ cái
        return {"k": "char", "v": shifted if upper else normal}
    if code in KEYPAD:
        return {"k": "char", "v": KEYPAD[code]}
    if code in CODE_TO_SPECIAL:
        return {"k": "special", "v": CODE_TO_SPECIAL[code]}
    return None


# ---- NGHE PHÍM -------------------------------------------------------------
def is_keyboard(dev):
    keys = dev.capabilities().get(e.EV_KEY, [])
    return dev.name != VIRTUAL_NAME and e.KEY_A in keys and e.KEY_Z in keys


def find_keyboards():
    """Trả về (danh sách bàn phím mở được, số thiết bị bị từ chối quyền)."""
    found, denied = [], 0
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except PermissionError:
            denied += 1
            continue
        except OSError:
            continue
        if is_keyboard(dev):
            found.append(dev)
        else:
            dev.close()
    return found, denied


class Listener(threading.Thread):
    """Nghe phím từ mọi bàn phím thật; gọi on_press(obj) cho mỗi lần nhấn (kể cả giữ phím)."""

    RESCAN_SEC = 3.0
    DUP_SEC = 0.03

    def __init__(self, on_press):
        super().__init__(daemon=True)
        self.on_press = on_press
        self.devices = {}  # path -> InputDevice
        self.shift_down = set()
        self.last = (None, None, None, 0.0)  # (path, code, value, time) để lọc trùng

    def rescan(self):
        found, denied = find_keyboards()
        for dev in found:
            if dev.path in self.devices:
                dev.close()
            else:
                self.devices[dev.path] = dev
                print("[i] Nghe bàn phím: %s (%s)" % (dev.name, dev.path))
        return denied

    def caps_on(self, dev):
        try:
            return e.LED_CAPSL in dev.leds()
        except OSError:
            return False

    def handle(self, dev, ev):
        if ev.type != e.EV_KEY:
            return
        # Phần mềm remap/macro (vd "Keyboard passthrough") có thể phát lại cùng phím qua
        # thiết bị ảo -> cùng phím từ thiết bị KHÁC trong DUP_SEC thì coi là bản sao.
        now = time.time()
        path, code, value, t = self.last
        self.last = (dev.path, ev.code, ev.value, now)
        if path != dev.path and code == ev.code and value == ev.value and now - t < self.DUP_SEC:
            return
        if ev.code in SHIFT_CODES:
            if ev.value == 0:
                self.shift_down.discard(ev.code)
            else:
                self.shift_down.add(ev.code)
        if ev.value == 0:  # nhả phím: giao thức hiện chỉ gửi nhấn
            return
        obj = translate(ev.code, bool(self.shift_down), self.caps_on(dev))
        if obj:
            self.on_press(obj)

    def run(self):
        last_scan = 0.0
        while True:
            now = time.time()
            if now - last_scan > self.RESCAN_SEC:
                self.rescan()
                last_scan = now
            if not self.devices:
                time.sleep(1)
                continue
            by_fd = {dev.fd: dev for dev in self.devices.values()}
            ready, _, _ = select.select(list(by_fd), [], [], 1.0)
            for fd in ready:
                dev = by_fd[fd]
                try:
                    for ev in dev.read():
                        self.handle(dev, ev)
                except OSError:  # rút bàn phím ra
                    print("[i] Mất bàn phím: %s" % dev.name)
                    self.devices.pop(dev.path, None)
                    try:
                        dev.close()
                    except OSError:
                        pass


# ---- BẤM PHÍM --------------------------------------------------------------
class Injector:
    """Bàn phím ảo qua /dev/uinput."""

    def __init__(self):
        codes = set(CHARS) | set(SPECIAL.values())
        self.ui = evdev.UInput({e.EV_KEY: sorted(codes)}, name=VIRTUAL_NAME)
        time.sleep(0.3)  # chờ compositor/X nhận thiết bị mới, kẻo mất phím đầu tiên

    def _key(self, code, value):
        self.ui.write(e.EV_KEY, code, value)
        self.ui.syn()

    def tap(self, obj):
        """Bấm + nhả 1 phím. Trả về False nếu phím không quy đổi được."""
        if not obj:
            return False
        if obj.get("k") == "char":
            hit = CHAR_TO_KEY.get(obj.get("v"))
            if not hit:
                return False
            code, shift = hit
        elif obj.get("k") == "special":
            name = SPECIAL_ALIASES.get(obj.get("v"), obj.get("v"))
            code, shift = SPECIAL.get(name), False
            if code is None:
                return False
        else:
            return False
        if shift:
            self._key(e.KEY_LEFTSHIFT, 1)
        self._key(code, 1)
        self._key(code, 0)
        if shift:
            self._key(e.KEY_LEFTSHIFT, 0)
        return True

    def close(self):
        self.ui.close()


# ---- KIỂM TRA QUYỀN --------------------------------------------------------
def setup_hint():
    if os.environ.get("APPIMAGE"):
        cmd = "%s --setup" % os.environ["APPIMAGE"]
    else:
        cmd = "sudo ./setup-linux.sh"
    return "Chạy 1 lần:  %s  rồi ĐĂNG XUẤT / đăng nhập lại." % cmd


def check_permissions(need_listen, need_inject):
    """In + trả về danh sách vấn đề về quyền (rỗng = đủ quyền cho các chế độ yêu cầu)."""
    problems = []
    if need_listen:
        found, denied = find_keyboards()
        for dev in found:
            dev.close()
        if not found:
            if denied:
                problems.append("Không đọc được bàn phím (/dev/input/event*): thiếu quyền nhóm 'input'.")
            else:
                problems.append("Không tìm thấy bàn phím nào trong /dev/input.")
    if need_inject and not os.access("/dev/uinput", os.W_OK):
        if os.path.exists("/dev/uinput"):
            problems.append("Không ghi được /dev/uinput -> máy này không tự bấm phím được.")
        else:
            problems.append("Chưa có /dev/uinput (module uinput chưa nạp).")
    if problems:
        problems.append(setup_hint())
        for p in problems:
            print("[!] " + p)
    return problems
