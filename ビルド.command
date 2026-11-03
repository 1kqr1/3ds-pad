#!/bin/zsh
# ダブルクリックで 3DS Pad.app をビルドする
cd "$(dirname "$0")"
./scripts/build_mac.sh && open dist
echo; echo "Enterで閉じます"; read
