"""アプリアイコン (assets/icon.icns と icon.png) を作る。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import io  # noqa: E402

from PIL import Image  # noqa: E402

from threeds_pad.server import make_icon  # noqa: E402

os.makedirs("assets", exist_ok=True)
img = Image.open(io.BytesIO(make_icon())).convert("RGBA")
img.save("assets/icon.png")
try:
    img.resize((1024, 1024), Image.LANCZOS).save("assets/icon.icns")
    print("assets/icon.icns を作成しました")
except Exception as e:  # noqa: BLE001
    print("icns を作れませんでした（アイコンなしでビルドします）:", e)
