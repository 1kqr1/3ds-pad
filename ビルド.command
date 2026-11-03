#!/bin/zsh
# ダブルクリックで 3DS Pad.app をビルドする
cd "$(dirname "$0")"
./scripts/build_mac.sh 2>&1 | tee build.log
if [ ${pipestatus[1]} -eq 0 ]; then open dist; fi
echo; echo "Enterで閉じます"; read
