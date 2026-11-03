"""Mac 側の小さなウィンドウ（QRコード・状態表示・権限ボタン）。"""
import base64
import io
import queue
import secrets
import tkinter as tk
from tkinter import ttk

import qrcode

from . import macos
from .server import Bridge, load_settings, save_settings

BG = "#1b1d22"
FG = "#e9e9ee"
SUB = "#8a8f9c"
OK = "#4cc38a"
NG = "#e8505b"


def qr_photo(text, box=6):
    qr = qrcode.QRCode(border=2, box_size=box)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return tk.PhotoImage(data=base64.b64encode(buf.getvalue()))


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("3DS Pad")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.logq = queue.Queue()
        self.settings = load_settings()
        self.mode = tk.StringVar(value="wifi")
        self.bridge = None
        self._qr_text = None
        self._build()
        self._start_bridge()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.after(300, self._tick)

    # ---- 画面 ---------------------------------------------------------------
    def _label(self, parent, text="", size=12, color=FG, bold=False, **kw):
        return tk.Label(parent, text=text, bg=BG, fg=color,
                        font=("Hiragino Sans", size, "bold" if bold else "normal"), **kw)

    def _build(self):
        r = self.root
        top = tk.Frame(r, bg=BG, padx=18, pady=14)
        top.pack(fill="both")

        self._label(top, "3DS Pad", 18, bold=True).grid(row=0, column=0, columnspan=2, sticky="w")
        self._label(top, "スマホのカメラでQRコードを読み取ってください", 11, SUB).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        left = tk.Frame(top, bg=BG)
        left.grid(row=2, column=0, sticky="n")
        self.qr_label = tk.Label(left, bg=BG)
        self.qr_label.pack()
        modes = tk.Frame(left, bg=BG)
        modes.pack(pady=6)
        for val, text in (("wifi", "Wi-Fi"), ("usb", "USB")):
            tk.Radiobutton(modes, text=text, value=val, variable=self.mode, command=self._update_qr,
                           bg=BG, fg=FG, selectcolor=BG, activebackground=BG, activeforeground=FG,
                           font=("Hiragino Sans", 12)).pack(side="left", padx=6)
        self.url_label = self._label(left, "", 10, SUB, wraplength=260)
        self.url_label.pack()
        btns = tk.Frame(left, bg=BG)
        btns.pack(pady=6)
        ttk.Button(btns, text="URLをコピー", command=self._copy).pack(side="left", padx=3)
        ttk.Button(btns, text="接続コードを作り直す", command=self._regen).pack(side="left", padx=3)

        right = tk.Frame(top, bg=BG, padx=16)
        right.grid(row=2, column=1, sticky="n")
        self.rows = {}
        for i, (key, title) in enumerate((
            ("screen", "画面収録の許可"),
            ("access", "アクセシビリティの許可"),
            ("azahar", "Azaharの下画面"),
            ("usb", "USB接続"),
            ("phone", "スマホ"),
        )):
            self._label(right, title, 12).grid(row=i, column=0, sticky="w", pady=3)
            v = self._label(right, "…", 12, SUB)
            v.grid(row=i, column=1, sticky="w", padx=10)
            self.rows[key] = v
        self.fix_screen = ttk.Button(right, text="設定を開く", command=self._fix_screen)
        self.fix_access = ttk.Button(right, text="設定を開く", command=self._fix_access)
        self.keys_label = self._label(right, "", 10, SUB, justify="left", wraplength=300)
        self.keys_label.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.hint = self._label(right, "", 10, SUB, justify="left", wraplength=300)
        self.hint.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self.log = tk.Text(r, height=5, bg="#121418", fg=SUB, relief="flat",
                           font=("Menlo", 10), padx=10, pady=6, highlightthickness=0)
        self.log.pack(fill="x", padx=18, pady=(0, 14))
        self.log.configure(state="disabled")

    # ---- サーバー -----------------------------------------------------------
    def _start_bridge(self):
        self.bridge = Bridge(self.settings, log=self.logq.put)
        try:
            self.bridge.start()
            self.logq.put(f"起動しました（ポート {self.bridge.port}）")
        except OSError as e:
            self.logq.put(f"ポート {self.bridge.port} を使えません: {e}")
        self._update_qr()
        self._update_keys()

    def _regen(self):
        self.bridge.stop()
        self.settings["token"] = secrets.token_urlsafe(8)
        save_settings(self.settings)
        self.logq.put("接続コードを作り直しました。スマホでQRを読み直してください")
        self.root.after(500, self._start_bridge)

    def _url(self):
        return self.bridge.usb_url if self.mode.get() == "usb" else self.bridge.wifi_url

    def _update_qr(self):
        url = self._url()
        if url != self._qr_text:
            self._qr_text = url
            self._qr_img = qr_photo(url)
            self.qr_label.configure(image=self._qr_img)
            self.url_label.configure(text=url)

    def _update_keys(self):
        text = f"キー割り当て: {self.bridge.key_path or '初期設定'}"
        if self.bridge.key_warnings:
            text += "\n⚠ " + "\n⚠ ".join(self.bridge.key_warnings[:4])
        self.keys_label.configure(text=text)
        self._keys_snapshot = self._key_sig()

    def _key_sig(self):
        b = self.bridge
        return (tuple(sorted(b.keys.items())), tuple(b.key_warnings), b.key_path)

    def _copy(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self._url())
        self.logq.put("URLをコピーしました")

    def _fix_screen(self):
        macos.request_screen_capture()
        macos.open_settings("screen")

    def _fix_access(self):
        macos.request_accessibility()
        macos.open_settings("accessibility")

    # ---- 定期更新 -----------------------------------------------------------
    def _set(self, key, ok, text):
        self.rows[key].configure(text=text, fg=OK if ok else NG)

    def _tick(self):
        b = self.bridge
        scr, acc = macos.has_screen_capture(), macos.has_accessibility()
        self._set("screen", scr, "OK" if scr else "未許可")
        self._set("access", acc, "OK" if acc else "未許可")
        (self.fix_screen.grid_remove if scr else lambda: self.fix_screen.grid(row=0, column=2))()
        (self.fix_access.grid_remove if acc else lambda: self.fix_access.grid(row=1, column=2))()

        if b.rect:
            self._set("azahar", True, f"検出 {int(b.rect[2])}×{int(b.rect[3])}")
        else:
            self._set("azahar", False, "見つかりません")
        self._set("usb", b.usb_state == "接続中", b.usb_state)
        n = len(b.clients)
        self._set("phone", n > 0, f"{n}台 接続中" if n else "未接続")

        hints = []
        if not (scr and acc):
            hints.append("許可を変えたら、このアプリを一度終了して開き直してください。")
        if not b.rect:
            hints.append("Azaharで 表示 → 画面レイアウト →「Separate Windows」にしてゲームを起動してください。")
        if b.rect and b.rect[2] < 400:
            hints.append("下画面ウィンドウを大きくすると、スマホの映像がきれいになります。")
        self.hint.configure(text="\n".join(hints))

        if self._key_sig() != getattr(self, "_keys_snapshot", None):
            self._update_keys()
        self._update_qr()

        while not self.logq.empty():
            self.log.configure(state="normal")
            self.log.insert("end", self.logq.get() + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(1000, self._tick)

    def quit(self):
        try:
            self.bridge.stop()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    App().run()
