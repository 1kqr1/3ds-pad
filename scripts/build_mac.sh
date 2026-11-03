#!/bin/bash
# 3DS Pad.app をビルドする（macOS 専用）
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
echo "== Python: $($PY --version)"
$PY -c "import tkinter" 2>/dev/null || { echo "この Python には tkinter がありません。python.org の Python を使ってください"; exit 1; }

$PY -m venv .venv
source .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt pyinstaller

# adb を同梱
if [ ! -x vendor/platform-tools/adb ]; then
  echo "== adb をダウンロード"
  mkdir -p vendor
  curl -fsSL -o vendor/pt.zip https://dl.google.com/android/repository/platform-tools-latest-darwin.zip
  (cd vendor && unzip -q -o pt.zip && rm -f pt.zip)
fi

python scripts/make_icon.py
ICON_ARG=()
[ -f assets/icon.icns ] && ICON_ARG=(--icon assets/icon.icns)

VERSION=$(python -c "import threeds_pad;print(threeds_pad.__version__)")
rm -rf build dist
pyinstaller --noconfirm --windowed --name "3DS Pad" \
  --osx-bundle-identifier io.github.threeds-pad \
  --add-data "threeds_pad/web:threeds_pad/web" \
  --add-binary "vendor/platform-tools/adb:adb" \
  --collect-submodules threeds_pad \
  "${ICON_ARG[@]}" run.py

PLIST="dist/3DS Pad.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$PLIST" 2>/dev/null || true
codesign --force --deep --sign - "dist/3DS Pad.app"

ARCH=$(uname -m)
(cd dist && ditto -c -k --keepParent "3DS Pad.app" "3DS-Pad-${VERSION}-mac-${ARCH}.zip")
echo
echo "✅ 完成: dist/3DS Pad.app"
echo "   配布用: dist/3DS-Pad-${VERSION}-mac-${ARCH}.zip"
