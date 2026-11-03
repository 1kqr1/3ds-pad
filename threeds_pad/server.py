"""スマホ向け Web サーバーと入力の橋渡し。"""
import asyncio
import io
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aiohttp import web, WSMsgType

from . import keymap, macos

APP_DIR = Path(os.path.expanduser("~/Library/Application Support/3DSPad"))
WEB_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "threeds_pad" / "web"
if not WEB_DIR.exists():
    WEB_DIR = Path(__file__).resolve().parent / "web"


# --- 設定（トークンとポートを保存） ------------------------------------------
def load_settings():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    f = APP_DIR / "settings.json"
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text())
        except ValueError:
            data = {}
    changed = False
    if not data.get("token"):
        data["token"] = secrets.token_urlsafe(8)
        changed = True
    data.setdefault("port", 8765)
    data.setdefault("fps", 30)
    data.setdefault("quality", 70)
    if changed:
        save_settings(data)
    return data


def save_settings(data):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    (APP_DIR / "settings.json").write_text(json.dumps(data, indent=2))


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def find_adb():
    """同梱の adb → PATH 上の adb の順に探す。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for cand in (base / "adb" / "adb", base / "platform-tools" / "adb"):
        if cand.exists():
            return str(cand)
    return shutil.which("adb")


class Bridge:
    def __init__(self, settings, log=print):
        self.s = settings
        self.log = log
        self.token = settings["token"]
        self.port = settings["port"]
        self.rect = None
        self.pid = None
        self.last_find = 0.0
        self.keys, self.key_warnings, self.key_path = keymap.load_keymap()
        self.key_mtime = self._mtime()
        self.clients = set()
        self.capturer = macos.Capturer()
        self.exec = ThreadPoolExecutor(max_workers=1)
        self.adb = find_adb()
        self.usb_state = "adb なし" if not self.adb else "待機中"
        self.loop = None
        self.runner = None
        self._stop = threading.Event()

    # ---- 状態 -------------------------------------------------------------
    @property
    def wifi_url(self):
        return f"http://{local_ip()}:{self.port}/?k={self.token}"

    @property
    def usb_url(self):
        return f"http://localhost:{self.port}/?k={self.token}"

    def _mtime(self):
        try:
            return os.path.getmtime(self.key_path) if self.key_path else 0
        except OSError:
            return 0

    def refresh(self):
        now = time.time()
        if now - self.last_find < 1.0 and self.rect:
            return
        self.last_find = now
        found = macos.find_bottom_window()
        if found:
            self.rect, self.pid = found[1], found[2]
        else:
            self.rect = None
        m = self._mtime()
        if m != self.key_mtime:            # Azahar の割り当て変更を反映
            self.key_mtime = m
            self.keys, self.key_warnings, self.key_path = keymap.load_keymap()
            self.log("キー割り当てを読み直しました")

    # ---- 入力 -------------------------------------------------------------
    def mouse(self, kind, nx, ny):
        if not self.rect:
            return
        x, y, w, h = self.rect
        px = x + max(0.0, min(1.0, nx)) * (w - 1)
        py = y + max(0.0, min(1.0, ny)) * (h - 1)
        macos.send_mouse(kind, px, py)

    def key(self, btn, down):
        code = self.keys.get(btn)
        if code is not None:
            macos.send_key(code, down)

    def grab(self):
        self.refresh()
        if not self.rect:
            return None
        return self.capturer.grab_jpeg(self.rect, quality=self.s.get("quality", 70))

    # ---- USB (adb reverse) ------------------------------------------------
    def _adb_loop(self):
        if not self.adb:
            return
        subprocess.run([self.adb, "start-server"], capture_output=True)
        while not self._stop.is_set():
            try:
                out = subprocess.run([self.adb, "devices"], capture_output=True, text=True, timeout=5).stdout
                devs = [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]
                unauth = any(l.strip().endswith("unauthorized") for l in out.splitlines()[1:])
                if devs:
                    for d in devs:
                        subprocess.run([self.adb, "-s", d, "reverse", f"tcp:{self.port}", f"tcp:{self.port}"],
                                       capture_output=True, timeout=5)
                    self.usb_state = "接続中"
                elif unauth:
                    self.usb_state = "スマホで「USBデバッグを許可」してください"
                else:
                    self.usb_state = "スマホ未接続"
            except Exception as e:  # noqa: BLE001
                self.usb_state = f"エラー: {e}"
            self._stop.wait(3)

    # ---- Web --------------------------------------------------------------
    def make_app(self):
        token = self.token
        index_html = (WEB_DIR / "index.html").read_text(encoding="utf-8")

        async def index(req):
            if req.query.get("k") != token:
                return web.Response(status=403, text="接続用のURLが違います。Mac の 3DS Pad に表示されたQRコードから開いてください。",
                                    content_type="text/plain", charset="utf-8")
            return web.Response(text=index_html, content_type="text/html")

        async def manifest(req):
            return web.json_response({
                "name": "3DS Pad", "short_name": "3DS Pad",
                "start_url": f"/?k={token}", "scope": "/",
                "display": "fullscreen", "orientation": "landscape",
                "background_color": "#1b1d22", "theme_color": "#1b1d22",
                "icons": [{"src": "/icon.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
            }, content_type="application/manifest+json")

        async def sw(req):
            return web.Response(text="self.addEventListener('install',e=>self.skipWaiting());"
                                     "self.addEventListener('activate',e=>e.waitUntil(clients.claim()));"
                                     "self.addEventListener('fetch',e=>{});",
                                content_type="application/javascript")

        async def icon(req):
            return web.Response(body=make_icon(), content_type="image/png")

        async def ws_handler(req):
            if req.query.get("k") != token:
                return web.Response(status=403)
            ws = web.WebSocketResponse(max_msg_size=0, heartbeat=10)
            await ws.prepare(req)
            self.clients.add(ws)
            self.log(f"スマホが接続しました（{req.remote}）")
            held, touching = set(), False
            macos.activate_pid(self.pid)
            try:
                async for msg in ws:
                    if msg.type != WSMsgType.TEXT:
                        continue
                    try:
                        m = json.loads(msg.data)
                    except ValueError:
                        continue
                    t = m.get("t")
                    if t in ("td", "tm", "tu"):
                        if t == "td":
                            macos.activate_pid(self.pid)
                            touching = True
                        elif t == "tu":
                            touching = False
                        self.mouse(t, float(m["x"]), float(m["y"]))
                    elif t == "k":
                        b, d = str(m.get("b")), bool(m.get("d"))
                        if d and b not in held:
                            held.add(b)
                            self.key(b, True)
                        elif not d and b in held:
                            held.discard(b)
                            self.key(b, False)
            finally:
                self.clients.discard(ws)
                for b in held:
                    self.key(b, False)
                if touching:
                    self.mouse("tu", 0.5, 0.5)
                self.log("スマホが切断されました")
            return ws

        async def broadcaster(app):
            loop = asyncio.get_running_loop()
            while True:
                interval = 1 / max(5, self.s.get("fps", 30))
                if not self.clients:
                    await loop.run_in_executor(self.exec, self.refresh)
                    await asyncio.sleep(0.5)
                    continue
                t0 = time.perf_counter()
                try:
                    data = await loop.run_in_executor(self.exec, self.grab)
                except Exception as e:  # noqa: BLE001
                    self.log(f"キャプチャ失敗: {e}")
                    data = None
                if data:
                    for ws in list(self.clients):
                        try:
                            await ws.send_bytes(data)
                        except Exception:  # noqa: BLE001
                            self.clients.discard(ws)
                else:
                    await asyncio.sleep(0.5)
                await asyncio.sleep(max(0, interval - (time.perf_counter() - t0)))

        async def on_startup(app):
            app["bc"] = asyncio.create_task(broadcaster(app))

        async def on_cleanup(app):
            app["bc"].cancel()

        app = web.Application()
        app.router.add_get("/", index)
        app.router.add_get("/manifest.webmanifest", manifest)
        app.router.add_get("/sw.js", sw)
        app.router.add_get("/icon.png", icon)
        app.router.add_get("/ws", ws_handler)
        app.on_startup.append(on_startup)
        app.on_cleanup.append(on_cleanup)
        return app

    def start(self):
        """バックグラウンドスレッドでサーバーと adb 監視を起動。"""
        threading.Thread(target=self._adb_loop, daemon=True).start()
        ready = threading.Event()
        err = []

        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.runner = web.AppRunner(self.make_app())
            try:
                self.loop.run_until_complete(self.runner.setup())
                site = web.TCPSite(self.runner, "0.0.0.0", self.port)
                self.loop.run_until_complete(site.start())
            except OSError as e:
                err.append(e)
                ready.set()
                return
            ready.set()
            self.loop.run_forever()

        threading.Thread(target=run, daemon=True).start()
        ready.wait(10)
        if err:
            raise err[0]

    def stop(self):
        self._stop.set()
        if self.loop and self.runner:
            fut = asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop)
            try:
                fut.result(3)
            except Exception:  # noqa: BLE001
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)


_ICON = None


def make_icon():
    global _ICON
    if _ICON is None:
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (512, 512), "#1b1d22")
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((106, 136, 406, 376), 24, fill="#000000", outline="#3a3e48", width=10)
        d.rectangle((40, 236, 110, 276), fill="#e9e9ee")
        d.rectangle((55, 221, 95, 291), fill="#e9e9ee")
        for cx, cy in ((456, 216), (486, 256), (426, 256), (456, 296)):
            d.ellipse((cx - 17, cy - 17, cx + 17, cy + 17), fill="#e8505b")
        buf = io.BytesIO()
        im.save(buf, "PNG")
        _ICON = buf.getvalue()
    return _ICON
