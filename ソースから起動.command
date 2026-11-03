#!/bin/zsh
# ビルドせずにそのまま起動する（開発・Intel Mac向け）
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
.venv/bin/python run.py "$@"
