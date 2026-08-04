#!/usr/bin/env bash
# ==================================================================
#  Build agent.py thanh file binary don le (KHONG can cai Python)
#  Yeu cau mot lan:  pip install pyinstaller pynput websocket-client
# ==================================================================
set -e
echo "Dang dong goi agent ..."
python3 -m PyInstaller --noconfirm clickdongbo-agent.spec || pyinstaller --noconfirm clickdongbo-agent.spec
cp -f config.json dist/config.json
echo
echo "XONG! File dung duoc tai:"
echo "  dist/clickdongbo-agent"
echo "  dist/config.json   (sua server / channel / name tai day)"
