"""起動口。引数なしならウィンドウ、--headless ならターミナルのみ。"""
import argparse
import time


def main():
    p = argparse.ArgumentParser(prog="3DS Pad")
    p.add_argument("--headless", action="store_true", help="ウィンドウを出さずにターミナルで動かす")
    args, _ = p.parse_known_args()   # macOS が付ける -psn_ 引数などは無視
    if not args.headless:
        from .gui import main as gui_main
        gui_main()
        return

    from . import macos
    from .server import Bridge, load_settings
    b = Bridge(load_settings())
    if not macos.has_screen_capture():
        print("⚠ 画面収録が未許可です"); macos.request_screen_capture()
    if not macos.has_accessibility():
        print("⚠ アクセシビリティが未許可です"); macos.request_accessibility()
    b.start()
    print("Wi-Fi:", b.wifi_url)
    print("USB  :", b.usb_url)
    for w in b.key_warnings:
        print("⚠", w)
    try:
        while True:
            time.sleep(5)
            print(f"[下画面 {'OK' if b.rect else 'なし'}] [USB {b.usb_state}] [スマホ {len(b.clients)}台]")
    except KeyboardInterrupt:
        b.stop()
