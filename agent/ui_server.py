# -*- coding: utf-8 -*-
"""
Giao diện web cục bộ cho agent: http://127.0.0.1:<ui_port>/  (chỉ máy này truy cập được).

  GET  /            -> ui.html (token nhúng sẵn trong trang)
  GET  /api/state   -> trạng thái agent (JSON)
  POST /api/action  -> {"action": "...", ...}  (bắt buộc header X-Agent-Token)

Bảo vệ:
  - chỉ bind 127.0.0.1;
  - kiểm tra Host (chặn DNS rebinding: trang lạ trỏ tên miền của nó về 127.0.0.1);
  - POST phải kèm token ngẫu nhiên mỗi lần chạy -> trang web khác đang mở trong trình duyệt
    không thể âm thầm đổi "server" (biến agent thành keylogger gửi phím ra ngoài).
"""

import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = secrets.token_urlsafe(24)


def _resource(name):
    # PyInstaller giải nén data vào sys._MEIPASS
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def start(port, get_state, do_action):
    """Chạy server ở luồng nền. Trả về URL, hoặc None nếu không mở được cổng."""
    with open(_resource("ui.html"), "r", encoding="utf-8") as f:
        page = f.read().replace("__AGENT_TOKEN__", TOKEN).encode("utf-8")
    allowed_hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # không spam console

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            if self.headers.get("Host", "") not in allowed_hosts:
                self._send(403, {"error": "host"})
                return False
            return True

        def do_GET(self):
            if not self._host_ok():
                return
            path = self.path.split("?")[0]
            if path == "/":
                self._send(200, page, "text/html; charset=utf-8")
            elif path == "/api/state":
                self._send(200, get_state())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok():
                return
            if self.path != "/api/action":
                return self._send(404, {"error": "not found"})
            if not secrets.compare_digest(self.headers.get("X-Agent-Token", ""), TOKEN):
                return self._send(403, {"error": "token"})
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 64 * 1024)
                data = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError("body phải là object")
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            try:
                result = do_action(data.get("action"), data)
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            self._send(200, {"ok": True, "result": result, "state": get_state()})

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        print("[!] Không mở được giao diện web ở cổng %d (%s)." % (port, e))
        return None
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d/" % port
