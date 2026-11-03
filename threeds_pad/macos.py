"""macOS 依存の処理: Azahar の下画面ウィンドウ検出、画面キャプチャ、入力送信、権限。"""
import io
import subprocess
import threading

import mss
from PIL import Image
import Quartz
from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps

TITLE_BAR = 28
OWNER_NAMES = ("azahar", "lime3ds", "citra")


def find_bottom_window(name_filter=None):
    """Azahar のウィンドウのうち縦横比が 4:3（下画面）に最も近いものを返す。

    戻り値: (score, (x, y, w, h), pid) または None
    """
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    best = None
    for w in wins:
        owner = (w.get("kCGWindowOwnerName") or "").lower()
        title = w.get("kCGWindowName") or ""
        if not any(n in owner for n in OWNER_NAMES) or w.get("kCGWindowLayer", 0) != 0:
            continue
        if name_filter and name_filter.lower() not in title.lower():
            continue
        b = w["kCGWindowBounds"]
        x, y, ww, hh = b["X"], b["Y"], b["Width"], b["Height"]
        ch = hh - TITLE_BAR
        if ww < 100 or ch < 80:
            continue
        score = abs(ww / ch - 4 / 3)
        if score > 0.25:            # ゲーム一覧などの横長ウィンドウは除外
            continue
        if best is None or score < best[0]:
            cx, cy, cw = x, y + TITLE_BAR, ww
            if cw / ch > 4 / 3:
                sw, sh = ch * 4 / 3, ch
            else:
                sw, sh = cw, cw * 3 / 4
            best = (score, (cx + (cw - sw) / 2, cy + (ch - sh) / 2, sw, sh), w.get("kCGWindowOwnerPID"))
    return best


class Capturer:
    """スレッドごとに mss を持つキャプチャ。"""

    def __init__(self):
        self._tls = threading.local()

    def grab_jpeg(self, rect, size=(640, 480), quality=70):
        if not hasattr(self._tls, "sct"):
            self._tls.sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        x, y, w, h = rect
        shot = self._tls.sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img = img.resize(size, Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()


_MOUSE = {
    "td": Quartz.kCGEventLeftMouseDown,
    "tm": Quartz.kCGEventLeftMouseDragged,
    "tu": Quartz.kCGEventLeftMouseUp,
}


def send_mouse(kind, px, py):
    ev = Quartz.CGEventCreateMouseEvent(None, _MOUSE[kind], (px, py), Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def send_key(code, down):
    ev = Quartz.CGEventCreateKeyboardEvent(None, code, bool(down))
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def activate_pid(pid):
    if not pid:
        return
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app and not app.isActive():
        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)


# --- 権限 -------------------------------------------------------------------
def has_screen_capture():
    try:
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except AttributeError:
        return True


def has_accessibility():
    try:
        return bool(Quartz.CGPreflightPostEventAccess())
    except AttributeError:
        return True


def request_screen_capture():
    try:
        Quartz.CGRequestScreenCaptureAccess()
    except AttributeError:
        pass


def request_accessibility():
    try:
        Quartz.CGRequestPostEventAccess()
    except AttributeError:
        pass


def open_settings(pane):
    urls = {
        "screen": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
        "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        "firewall": "x-apple.systempreferences:com.apple.preference.security?Firewall",
    }
    subprocess.Popen(["open", urls[pane]])
